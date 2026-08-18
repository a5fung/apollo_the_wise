"""2026-08-18 -- forward alert-day minute-path capture (ep_profitability_program.md
§0g, the conversion rehearsal). `persist_alert_day_paths` only ever captured DAY 0
of an EP alert; the rehearsal found the winners we surface run 7-21 sessions past
the alert day, and in 3 of 5 cases from a base that formed DAYS LATER, below the
EP-day low — a timing problem only a delayed-entry read can see, and that read
needs minute bars for the sessions AFTER the alert, which nothing captured. This
tests the fix: `order_manager.persist_forward_alert_paths` extends the SAME
fetch/persist path forward, bounded, for names stopped out of a live position.

THE LINE: capture only. No test here touches or asserts on any
detection/entry/sizing/ordering behavior — only what gets fetched/persisted/
skipped and why.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from tests.conftest import make_mock_pool
from agents.market_intelligence.broker import order_manager as om

_ET = ZoneInfo("America/New_York")


# ── trading_sessions_elapsed — pure ────────────────────────────────────────────


def test_same_day_is_zero_sessions():
    assert om.trading_sessions_elapsed(date(2026, 8, 7), date(2026, 8, 7)) == 0


def test_as_of_before_alert_is_zero_never_negative():
    assert om.trading_sessions_elapsed(date(2026, 8, 7), date(2026, 8, 1)) == 0


def test_next_weekday_is_one_session():
    assert om.trading_sessions_elapsed(date(2026, 8, 7), date(2026, 8, 10)) == 1  # Fri -> Mon


def test_counts_weekdays_only_skips_the_weekend():
    # Fri 8/7 -> Tue 8/11: Mon 8/10 + Tue 8/11 = 2 sessions, weekend not counted
    assert om.trading_sessions_elapsed(date(2026, 8, 7), date(2026, 8, 11)) == 2


def test_25_and_26_session_boundary_dates():
    """Pins the exact calendar dates the window-bound tests below rely on."""
    assert om.trading_sessions_elapsed(date(2026, 8, 7), date(2026, 9, 11)) == 25
    assert om.trading_sessions_elapsed(date(2026, 8, 7), date(2026, 9, 14)) == 26


# ── persist_forward_alert_paths ────────────────────────────────────────────────


def _full_day(ticker, day):
    base = datetime(day.year, day.month, day.day, 9, 30, tzinfo=_ET)
    return [{"t_et": base + timedelta(minutes=i), "open": 1, "high": 1, "low": 1,
             "close": 1, "volume": 100, "vwap": None} for i in range(390)]


def _wire(monkeypatch, *, population_rows, bar_counts=None, fetched_bars=None):
    """Mirrors test_capture_retention_2026_08_15.py's `_wire_om` for the
    forward-capture job. `population_rows`: list of {"ticker", "alert_date"}
    dicts the (mocked) population SQL returns. `bar_counts`: ticker ->
    already-persisted bar count for the fetch day. `fetched_bars`: ticker ->
    bars get_minute_bars_range returns (or an Exception instance to raise)."""
    bar_counts = bar_counts or {}
    fetched_bars = fetched_bars or {}
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=population_rows)

    async def _fetchval(sql, ticker, *a):
        return bar_counts.get(ticker, 0)
    conn.fetchval = _fetchval

    async def _pool():
        return pool
    monkeypatch.setattr(om, "get_pool", _pool)

    calls, persisted, logged = [], [], []

    async def _get_range(ticker, start, end):
        calls.append((ticker, start, end))
        if isinstance(fetched_bars.get(ticker), Exception):
            raise fetched_bars[ticker]
        return fetched_bars.get(ticker, [])

    async def _persist(ticker, bars):
        persisted.append((ticker, len(bars)))

    monkeypatch.setattr(om.alpaca, "get_minute_bars_range", _get_range)
    monkeypatch.setattr(om.alpaca, "persist_intraday_bars", _persist)

    async def _log(event_type, summary, detail=""):
        logged.append((event_type, summary))
    monkeypatch.setattr(om, "log_audit_event", _log)
    return calls, persisted, logged, conn


def test_population_sql_selects_stopped_out_live_trades_only(monkeypatch):
    """The population must be `mi_exit_path_shadow` stop-outs, not every alert
    (that's the day-0 job's much broader population) — behavioral, not a
    docstring check: asserts on the SQL statement actually sent to the DB."""
    calls, _, _, conn = _wire(monkeypatch, population_rows=[])
    asyncio.run(om.persist_forward_alert_paths(target_date=date(2026, 8, 11)))
    sql = conn.fetch.call_args[0][0]
    assert "mi_exit_path_shadow" in sql
    assert "exit_reason = 'stop_hit'" in sql
    assert "is_exit_day = true" in sql
    assert calls == []  # empty population -> no fetches


def test_day_zero_is_skipped_owned_by_the_other_job(monkeypatch):
    """alert_date == target_date -> 0 sessions elapsed -> this job must NOT
    fetch it (persist_alert_day_paths already owns day 0); fetching here too
    would double the API budget for nothing."""
    rows = [{"ticker": "FIGS", "alert_date": date(2026, 8, 7)}]
    calls, persisted, _, _ = _wire(monkeypatch, population_rows=rows)
    out = asyncio.run(om.persist_forward_alert_paths(target_date=date(2026, 8, 7)))
    assert calls == [] and persisted == []
    assert out["population"] == 0 and out["window_closed"] == 0


def test_within_window_fetches_and_persists(monkeypatch):
    """2 sessions past the alert (Fri 8/7 -> Tue 8/11), well inside the 25-session
    bound: must fetch and persist TODAY's (8/11) bars."""
    rows = [{"ticker": "FIGS", "alert_date": date(2026, 8, 7)}]
    target = date(2026, 8, 11)
    calls, persisted, _, _ = _wire(
        monkeypatch, population_rows=rows,
        fetched_bars={"FIGS": _full_day("FIGS", target)})
    out = asyncio.run(om.persist_forward_alert_paths(target_date=target))
    assert [t for t, _, _ in calls] == ["FIGS"]
    (_, start, end), = calls
    assert (start.year, start.month, start.day) == (2026, 8, 11)  # fetches TODAY, not the alert day
    assert (start.hour, start.minute) == (9, 30) and (end.hour, end.minute) == (16, 0)
    assert persisted == [("FIGS", 390)]
    assert out["population"] == 1 and out["fetched"] == 1 and out["window_closed"] == 0


def test_exactly_25_sessions_still_captured_26_is_not(monkeypatch):
    """Pins the bound precisely at the named constant: the window is INCLUSIVE
    of FORWARD_CAPTURE_WINDOW_SESSIONS (25) and excludes the session after it."""
    assert om.FORWARD_CAPTURE_WINDOW_SESSIONS == 25
    rows = [{"ticker": "AT25", "alert_date": date(2026, 8, 7)},
            {"ticker": "AT26", "alert_date": date(2026, 8, 7)}]

    calls25, _, _, _ = _wire(
        monkeypatch, population_rows=[rows[0]],
        fetched_bars={"AT25": _full_day("AT25", date(2026, 9, 11))})
    out25 = asyncio.run(om.persist_forward_alert_paths(target_date=date(2026, 9, 11)))
    assert out25["population"] == 1 and out25["window_closed"] == 0
    assert [t for t, _, _ in calls25] == ["AT25"]

    calls26, _, _, _ = _wire(monkeypatch, population_rows=[rows[1]])
    out26 = asyncio.run(om.persist_forward_alert_paths(target_date=date(2026, 9, 14)))
    assert out26["population"] == 0 and out26["window_closed"] == 1
    assert calls26 == []  # window closed -> no API call at all


def test_already_covered_skips_without_api_call(monkeypatch):
    """Idempotent per-day: existing >= _PATH_MIN_DAY_BARS bars for today ->
    no refetch, mirrors persist_alert_day_paths' own contract."""
    rows = [{"ticker": "COVERED", "alert_date": date(2026, 8, 7)}]
    target = date(2026, 8, 11)
    calls, _, _, _ = _wire(
        monkeypatch, population_rows=rows,
        bar_counts={"COVERED": om._PATH_MIN_DAY_BARS})
    out = asyncio.run(om.persist_forward_alert_paths(target_date=target))
    assert calls == []
    assert out["already_covered"] == 1 and out["fetched"] == 0


def test_thin_day_logs_coverage_gap_with_session_number(monkeypatch):
    rows = [{"ticker": "THIN", "alert_date": date(2026, 8, 7)}]
    target = date(2026, 8, 11)
    _, persisted, logged, _ = _wire(
        monkeypatch, population_rows=rows,
        fetched_bars={"THIN": _full_day("THIN", target)[:40]})
    out = asyncio.run(om.persist_forward_alert_paths(target_date=target))
    assert persisted == [("THIN", 40)]
    assert out["thin"] == 1
    assert any(ev == "path_coverage_gap" and "THIN" in s and "session 2" in s
               for ev, s in logged)


def test_one_bad_ticker_does_not_kill_the_run(monkeypatch):
    """Fail-soft: a fetch failure for one ticker must not stop the rest of the
    day's forward capture."""
    rows = [{"ticker": "BAD", "alert_date": date(2026, 8, 7)},
            {"ticker": "GOOD", "alert_date": date(2026, 8, 7)}]
    target = date(2026, 8, 11)
    _, persisted, _, _ = _wire(
        monkeypatch, population_rows=rows,
        fetched_bars={"BAD": RuntimeError("api down"),
                      "GOOD": _full_day("GOOD", target)})
    out = asyncio.run(om.persist_forward_alert_paths(target_date=target))
    assert ("GOOD", 390) in persisted
    assert out["errors"] == 1 and out["fetched"] == 1


def test_population_query_bounds_the_lookback_window():
    """The SQL floor must reference FORWARD_CAPTURE_WINDOW_SESSIONS (not a
    hardcoded number) so the two stay in lockstep if the constant ever changes."""
    import inspect
    src = inspect.getsource(om.persist_forward_alert_paths)
    assert "FORWARD_CAPTURE_WINDOW_SESSIONS * 2" in src


# ── scheduler wiring ────────────────────────────────────────────────────────────


def test_scheduler_registers_forward_alert_path_persist_as_execution_owned():
    from agents.market_intelligence import scheduler as sched
    assert "forward_alert_path_persist" in sched.EXECUTION_OWNED_JOB_IDS
    import inspect
    src = inspect.getsource(sched.start_scheduler)
    assert 'id="forward_alert_path_persist"' in src


def test_forward_job_scheduled_after_day_zero_job_never_overlapping():
    """16:24 ET, 2 minutes after the 16:22 ET day-0 job -- must never run
    concurrently with it (both touch mi_intraday_bars for potentially
    overlapping tickers)."""
    import inspect
    from agents.market_intelligence import scheduler as sched
    src = inspect.getsource(sched.start_scheduler)
    idx = src.index('id="forward_alert_path_persist"')
    block = src[max(0, idx - 400):idx]
    assert "hour=16, minute=24" in block
