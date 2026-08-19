"""#562 — behavioral tests for scripts/backfill_forward_minute_bars_562.py, the
one-time historical backfill of forward-window minute bars for stopped-out EP
names (see that script's module docstring for the full "why").

THE LINE: capture only. No test here touches or asserts on any
detection/entry/sizing/ordering behavior — only what gets fetched/persisted/
skipped/resumed and why. No network, no real DB — everything below is wired
against `tests.conftest.make_mock_pool`, mirroring
`test_forward_alert_path_persist_2026_08_18.py`'s own harness for the sibling
job this script backfills the history of.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from tests.conftest import make_mock_pool
from scripts import backfill_forward_minute_bars_562 as bfm

_ET = ZoneInfo("America/New_York")


def _full_day():
    base = datetime(2026, 1, 1, 9, 30, tzinfo=_ET)
    return [{"t_et": base + timedelta(minutes=i), "open": 1, "high": 1, "low": 1,
             "close": 1, "volume": 100, "vwap": None} for i in range(390)]


def _wire(monkeypatch, *, population_rows=None, live_only_population_rows=None,
          forward_days=None, bar_counts=None, fetched_bars=None):
    """population_rows: rows the mi_live_trades population query returns (dicts
    with ticker/alert_date/account_mode). forward_days: ticker -> list[date] the
    (fake) mi_daily_closes query has available. bar_counts: (ticker, date) ->
    already-persisted bar count. fetched_bars: ticker -> bars get_minute_bars_range
    returns (or an Exception instance to raise); defaults to a full 390-bar day."""
    population_rows = population_rows or []
    forward_days = forward_days or {}
    bar_counts = bar_counts or {}
    fetched_bars = fetched_bars or {}
    pool, conn = make_mock_pool()

    fetch_calls = []

    async def _fetch(sql, *args):
        fetch_calls.append((sql, args))
        if "mi_live_trades" in sql:
            return population_rows
        if "mi_exit_path_shadow" in sql:
            return live_only_population_rows or []
        if "mi_daily_closes" in sql:
            # Deliberately does NOT re-filter by alert_date here (that would let a
            # broken WHERE clause pass silently) — it only applies the LIMIT/window,
            # exactly what a real DB does with whatever days are fed in. Callers that
            # care about the >alert_date semantics assert on the SQL TEXT instead.
            ticker, alert_date, window = args
            return [{"trade_date": d} for d in forward_days.get(ticker, [])[:window]]
        raise AssertionError(f"unexpected fetch SQL: {sql}")
    conn.fetch = AsyncMock(side_effect=_fetch)

    async def _fetchval(sql, ticker, day):
        return bar_counts.get((ticker, day), 0)
    conn.fetchval = AsyncMock(side_effect=_fetchval)

    async def _pool():
        return pool
    monkeypatch.setattr(bfm, "get_pool", _pool)

    range_calls, persisted = [], []

    async def _get_range(ticker, start, end):
        range_calls.append((ticker, start.date()))
        v = fetched_bars.get(ticker)
        if isinstance(v, Exception):
            raise v
        return v if v is not None else _full_day()

    async def _persist(ticker, bars):
        persisted.append((ticker, len(bars)))

    monkeypatch.setattr(bfm.alpaca, "get_minute_bars_range", _get_range)
    monkeypatch.setattr(bfm.alpaca, "persist_intraday_bars", _persist)

    sleeps = []

    async def _sleep(s):
        sleeps.append(s)
    monkeypatch.setattr(bfm.asyncio, "sleep", _sleep)

    return range_calls, persisted, sleeps, conn, fetch_calls


# ── population / cohort selection ───────────────────────────────────────────


def test_population_sql_is_magna53_stop_hit_paper_and_live_by_default(monkeypatch):
    """Default population must be built from mi_live_trades directly (paper+live),
    not the narrower mi_exit_path_shadow (live-only) population — the whole point
    of widening scope (see module docstring). Behavioral: assert on the actual
    SQL sent."""
    _, _, _, conn, fetch_calls = _wire(monkeypatch, population_rows=[])
    asyncio.run(bfm.run_backfill())
    sql = fetch_calls[0][0]
    assert "mi_live_trades" in sql
    assert "magna53" in sql
    assert "'stop_hit'" in sql
    assert "entry_price IS NOT NULL" in sql
    assert "status IN ('closed', 'stopped')" in sql


def test_live_only_flag_matches_the_narrower_shadow_population(monkeypatch):
    """--live-only reproduces persist_forward_alert_paths' own population exactly."""
    _, _, _, conn, fetch_calls = _wire(monkeypatch, live_only_population_rows=[])
    asyncio.run(bfm.run_backfill(live_only=True))
    sql = fetch_calls[0][0]
    assert "mi_exit_path_shadow" in sql
    assert "is_exit_day = true" in sql
    assert "exit_reason = 'stop_hit'" in sql
    assert "mi_live_trades" not in sql


def test_empty_population_fetches_nothing(monkeypatch):
    range_calls, persisted, _, _, _ = _wire(monkeypatch, population_rows=[])
    out = asyncio.run(bfm.run_backfill())
    assert range_calls == []
    assert persisted == []
    assert out == {"population": 0, "ticker_days_targeted": 0, "already_covered": 0,
                    "fetched": 0, "thin": 0, "api_calls": 0}


# ── window / day-0 exclusion ────────────────────────────────────────────────


def test_day_zero_is_excluded_strictly_after_alert_date(monkeypatch):
    """forward_session_days's SQL must ask for trade_date > alert_date (strict),
    never >=, so the alert day itself (persist_alert_day_paths' job) is never
    touched by this script. Asserted on the actual SQL text (not on the fake's
    behavior — the fake deliberately does not re-filter by date, see _wire) so a
    regressed WHERE clause is caught here, not masked by the test harness."""
    ticker, alert = "FIGS", date(2026, 8, 7)
    _, _, _, _, fetch_calls = _wire(
        monkeypatch,
        population_rows=[{"ticker": ticker, "alert_date": alert, "account_mode": "live"}],
        forward_days={ticker: [alert + timedelta(days=1)]},
        bar_counts={},
    )
    asyncio.run(bfm.run_backfill())
    daily_closes_calls = [(sql, args) for sql, args in fetch_calls if "mi_daily_closes" in sql]
    assert len(daily_closes_calls) == 1
    sql, args = daily_closes_calls[0]
    assert "trade_date > $2" in sql
    assert "trade_date >= $2" not in sql
    assert args == (ticker, alert, bfm.FORWARD_CAPTURE_WINDOW_SESSIONS)


def test_window_capped_at_25_sessions(monkeypatch):
    """Even when 30 forward trading days exist, only the SQL-enforced 25-session
    window is ever requested."""
    ticker, alert = "WULF", date(2026, 7, 6)
    all_days = [alert + timedelta(days=i) for i in range(1, 31)]  # 30 candidate days
    range_calls, _, _, _, _ = _wire(
        monkeypatch,
        population_rows=[{"ticker": ticker, "alert_date": alert, "account_mode": "live"}],
        forward_days={ticker: all_days},
    )
    out = asyncio.run(bfm.run_backfill())
    assert out["ticker_days_targeted"] == 25
    assert len(range_calls) == 25


# ── idempotency / resume ────────────────────────────────────────────────────


def test_already_covered_days_are_skipped_no_api_call(monkeypatch):
    ticker, alert = "TEAM", date(2026, 8, 7)
    days = [alert + timedelta(days=i) for i in (1, 2, 3)]
    range_calls, persisted, _, _, _ = _wire(
        monkeypatch,
        population_rows=[{"ticker": ticker, "alert_date": alert, "account_mode": "live"}],
        forward_days={ticker: days},
        bar_counts={(ticker, days[0]): 391, (ticker, days[1]): 0, (ticker, days[2]): 45},
    )
    out = asyncio.run(bfm.run_backfill())
    # days[0] clears the 300-bar floor (391) and is skipped; days[1] (0) and
    # days[2] (45, still thin) are both below the floor and must be fetched
    assert range_calls == [(ticker, days[1]), (ticker, days[2])]
    assert out["already_covered"] == 1


def test_resume_after_full_prior_run_makes_zero_new_calls(monkeypatch):
    """The resumability contract: re-running once every targeted day already has
    >= 300 bars persisted must make ZERO further API calls."""
    ticker, alert = "BW", date(2026, 8, 11)
    days = [alert + timedelta(days=i) for i in (1, 2, 3, 4, 5)]
    range_calls, _, _, _, _ = _wire(
        monkeypatch,
        population_rows=[{"ticker": ticker, "alert_date": alert, "account_mode": "live"}],
        forward_days={ticker: days},
        bar_counts={(ticker, d): 391 for d in days},  # a completed prior run
    )
    out = asyncio.run(bfm.run_backfill())
    assert range_calls == []
    assert out["already_covered"] == 5
    assert out["fetched"] == 0
    assert out["api_calls"] == 0


def test_resume_only_reattempts_the_missing_day(monkeypatch):
    """Mid-run crash simulation: 2 of 3 days already landed; a re-run must fetch
    only the missing one, not redo the first two."""
    ticker, alert = "NET", date(2026, 8, 7)
    days = [alert + timedelta(days=i) for i in (1, 2, 3)]
    range_calls, persisted, _, _, _ = _wire(
        monkeypatch,
        population_rows=[{"ticker": ticker, "alert_date": alert, "account_mode": "live"}],
        forward_days={ticker: days},
        bar_counts={(ticker, days[0]): 391, (ticker, days[1]): 391, (ticker, days[2]): 0},
    )
    out = asyncio.run(bfm.run_backfill())
    assert range_calls == [(ticker, days[2])]
    assert persisted == [(ticker, 390)]
    assert out["already_covered"] == 2
    assert out["fetched"] == 1


# ── dry-run / limit ──────────────────────────────────────────────────────────


def test_dry_run_makes_zero_fetch_calls(monkeypatch):
    ticker, alert = "MRVL", date(2026, 8, 19)
    days = [alert + timedelta(days=i) for i in (1, 2)]
    range_calls, persisted, _, _, _ = _wire(
        monkeypatch,
        population_rows=[{"ticker": ticker, "alert_date": alert, "account_mode": "live"}],
        forward_days={ticker: days},
        bar_counts={},
    )
    out = asyncio.run(bfm.run_backfill(dry_run=True))
    assert range_calls == []
    assert persisted == []
    assert out["api_calls"] == 0
    assert out["ticker_days_targeted"] == 2


def test_limit_caps_actual_fetch_calls(monkeypatch):
    ticker, alert = "QBTS", date(2026, 7, 27)
    days = [alert + timedelta(days=i) for i in (1, 2, 3, 4)]
    range_calls, _, _, _, _ = _wire(
        monkeypatch,
        population_rows=[{"ticker": ticker, "alert_date": alert, "account_mode": "live"}],
        forward_days={ticker: days},
        bar_counts={},
    )
    out = asyncio.run(bfm.run_backfill(limit=2))
    assert len(range_calls) == 2
    assert out["api_calls"] == 2
    # the other 2 remain uncovered for the next run — not silently dropped
    assert out["already_covered"] == 0


# ── failure handling ─────────────────────────────────────────────────────────


def test_one_failed_ticker_day_does_not_abort_the_run(monkeypatch):
    t1, t2 = "SMCI", "NVCR"
    a1, a2 = date(2026, 7, 22), date(2026, 7, 23)
    d1, d2 = a1 + timedelta(days=1), a2 + timedelta(days=1)
    range_calls, persisted, _, _, _ = _wire(
        monkeypatch,
        population_rows=[
            {"ticker": t1, "alert_date": a1, "account_mode": "live"},
            {"ticker": t2, "alert_date": a2, "account_mode": "live"},
        ],
        forward_days={t1: [d1], t2: [d2]},
        bar_counts={},
        fetched_bars={t1: RuntimeError("simulated Alpaca failure")},
    )
    out = asyncio.run(bfm.run_backfill())
    assert (t1, d1) in range_calls
    assert (t2, d2) in range_calls  # the second ticker still gets processed
    assert out["thin"] >= 1
    assert out["fetched"] == 1  # t2 succeeded
    assert persisted == [(t2, 390)]


def test_empty_bars_returned_counts_as_thin_not_fetched(monkeypatch):
    ticker, alert = "THC", date(2026, 7, 24)
    day = alert + timedelta(days=1)
    range_calls, persisted, _, _, _ = _wire(
        monkeypatch,
        population_rows=[{"ticker": ticker, "alert_date": alert, "account_mode": "live"}],
        forward_days={ticker: [day]},
        bar_counts={},
        fetched_bars={ticker: []},
    )
    out = asyncio.run(bfm.run_backfill())
    assert range_calls == [(ticker, day)]
    assert persisted == []
    assert out["thin"] == 1
    assert out["fetched"] == 0


# ── rate limiting ─────────────────────────────────────────────────────────────


def test_sleeps_once_per_actual_fetch_not_per_skipped_day(monkeypatch):
    ticker, alert = "WKC", date(2026, 7, 24)
    days = [alert + timedelta(days=i) for i in (1, 2, 3)]
    _, _, sleeps, _, _ = _wire(
        monkeypatch,
        population_rows=[{"ticker": ticker, "alert_date": alert, "account_mode": "live"}],
        forward_days={ticker: days},
        bar_counts={(ticker, days[0]): 391},  # 1 already covered, 2 need a fetch
    )
    asyncio.run(bfm.run_backfill())
    assert len(sleeps) == 2
    assert all(s == bfm._REQUEST_DELAY_S for s in sleeps)
