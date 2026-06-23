"""#361 (2026-06-23) — partial-exit SPLIT to a market-hours (3:45 PM) trigger.

The Day 3-5 partial-profit decision was moved OUT of the 4:45 PM EOD
`update_open_positions_live` job into `run_partial_exits` (3:45 PM), so the
partial's stop-replace settles intraday instead of parking in
`pending_replace` after the close. These tests freeze the two correctness
properties the split must hold:

  1. NO DOUBLE-FIRE — the partial fires in run_partial_exits and NEVER in the
     4:45 job (which passes skip_partial_decision=True). execute_partial_exit
     is reached by exactly one of the two jobs.
  2. PARTIAL LOGIC UNCHANGED — run_partial_exits reuses apply_daily_exit_step
     (the single source of truth) and acts on step.partial_fired /
     step.partial_shares; the 4:45 job suppresses the decision via the
     skip_partial_decision flag (not by re-implementing it).

Run: python -m pytest tests/test_partial_exit_split_361.py -v
"""
import asyncio
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.market_intelligence.broker import live_tracker
from agents.market_intelligence.broker.exit_logic import ExitStep


# ── Fake async DB pool ───────────────────────────────────────────────────────


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows
        self.executed = []

    async def fetch(self, *_a, **_k):
        return self._rows

    async def execute(self, *a, **_k):
        self.executed.append(a)


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _FakeAcquire(self._conn)


def _trade_row():
    # A Day-4 open position eligible for a partial (90 shares filled).
    return {
        "id": 1,
        "ticker": "TEST",
        "alert_date": date(2026, 6, 18),  # 3 trading days before "today"
        "remaining_shares": 90,
        "entry_price": 100.0,
        "hard_stop": 95.0,
        "stop_price": 95.0,
        "partial_taken": False,
        "breakeven_active": False,
        "exits": [],
        "running_closes": [101.0] * 25,  # enough history for SMA
    }


def _partial_step():
    # A step where the partial fired (30 of 90 shares), position stays open.
    return ExitStep(
        action="partial_only", closed=False,
        close_reason=None, close_price=None, close_shares=None, close_pnl=None,
        partial_fired=True, partial_shares=30,
        partial_price=110.0, partial_pnl=300.0,
        effective_stop=100.0, active_sma=101.0,
        bar_low=108.0, bar_close=110.0, hold_days=4,
        new_remaining=60, new_partial_taken=True, new_breakeven_active=True,
        new_running_closes=[101.0] * 25 + [110.0], new_exits=[], new_total_pnl=300.0,
    )


def _install_common(monkeypatch, step, exec_spy, *, captured_kwargs=None):
    """Wire up the shared fakes; record apply_daily_exit_step kwargs."""
    conn = _FakeConn([_trade_row()])
    monkeypatch.setattr(live_tracker, "get_pool",
                        lambda: asyncio.sleep(0, result=_FakePool(conn)))
    monkeypatch.setattr(live_tracker, "et_today", lambda: date(2026, 6, 23))
    monkeypatch.setattr(live_tracker, "get_index_history",
                        lambda *_a, **_k: asyncio.sleep(0, result=[{"l": 108.0, "c": 110.0, "h": 111.0, "o": 109.0}]))

    def _ades(state, bar, today, **kwargs):
        if captured_kwargs is not None:
            captured_kwargs.append(kwargs)
        return step
    monkeypatch.setattr(live_tracker, "apply_daily_exit_step", _ades)

    monkeypatch.setattr(live_tracker, "execute_partial_exit",
                        lambda *a, **k: exec_spy(*a, **k))
    # Suppress real broker / telegram side effects in the 4:45 path.
    monkeypatch.setattr(live_tracker, "update_stop",
                        lambda *a, **k: asyncio.sleep(0, result=True))
    monkeypatch.setattr(live_tracker, "execute_full_exit",
                        lambda *a, **k: asyncio.sleep(0, result=True))
    monkeypatch.setattr(live_tracker, "send_live_trade_summary",
                        lambda *a, **k: asyncio.sleep(0))
    return conn


# ── Property 1: run_partial_exits TAKES the partial ──────────────────────────


def test_run_partial_exits_fires_partial(monkeypatch):
    calls = []

    async def exec_spy(trade_id, shares, **k):
        calls.append((trade_id, shares))
        return True

    kwargs_seen = []
    _install_common(monkeypatch, _partial_step(), exec_spy,
                    captured_kwargs=kwargs_seen)

    results = asyncio.run(live_tracker.run_partial_exits())

    assert calls == [(1, 30)], f"partial not taken in 3:45 job: {calls}"
    assert results[0]["action"] == "partial_submitted"
    # SINGLE SOURCE OF TRUTH: it reuses apply_daily_exit_step WITHOUT
    # skip_partial_decision (the partial decision is alive here).
    assert kwargs_seen, "apply_daily_exit_step not called"
    assert not kwargs_seen[0].get("skip_partial_decision", False), \
        "3:45 job must NOT skip the partial decision"
    # skip_hard_stop_close=True so an intraday wick to hard_stop doesn't
    # short-circuit before the partial branch (matches the 4:45 post-verify
    # re-run; the real resting Alpaca stop is the actual stop mechanism).
    assert kwargs_seen[0].get("skip_hard_stop_close") is True, \
        "3:45 job must pass skip_hard_stop_close=True"


def test_run_partial_exits_writes_no_db_rows(monkeypatch):
    # The 3:45 job persists NOTHING (finalize_partial_exit on WS fill + the
    # 4:45 job own all state writes; writing running_closes here would
    # double-append today's close and corrupt the SMA basis).
    async def exec_spy(trade_id, shares, **k):
        return True

    conn = _install_common(monkeypatch, _partial_step(), exec_spy)
    asyncio.run(live_tracker.run_partial_exits())
    assert conn.executed == [], f"3:45 job must not UPDATE mi_live_trades: {conn.executed}"


# ── Property 2: the 4:45 job NEVER takes a partial (no double-fire) ──────────


def test_eod_job_skips_partial_decision_and_never_fires(monkeypatch):
    calls = []

    async def exec_spy(trade_id, shares, **k):
        calls.append((trade_id, shares))
        return True

    kwargs_seen = []
    # Even if the (suppressed) decision WOULD have fired, the 4:45 job must
    # pass skip_partial_decision=True. We assert the flag is set AND that
    # execute_partial_exit is never reached from this job.
    _install_common(monkeypatch, _partial_step(), exec_spy,
                    captured_kwargs=kwargs_seen)

    asyncio.run(live_tracker.update_open_positions_live())

    assert calls == [], f"4:45 job DOUBLE-FIRED the partial: {calls}"
    assert kwargs_seen, "apply_daily_exit_step not called by 4:45 job"
    for kw in kwargs_seen:
        assert kw.get("skip_partial_decision") is True, \
            f"4:45 job must pass skip_partial_decision=True, got {kw}"


def test_wick_day_still_fires_partial_with_real_decision(monkeypatch):
    # REGRESSION (advisor #361): a Day-4 position whose forming 3:45 bar wicked
    # to/through its hard_stop intraday but recovered green must STILL take the
    # partial. Without skip_hard_stop_close=True, apply_daily_exit_step would
    # short-circuit at its hard-stop close (partial_fired=False) and the partial
    # would be silently dropped. This test lets the REAL decision function run.
    calls = []

    async def exec_spy(trade_id, shares, **k):
        calls.append((trade_id, shares))
        return True

    # Trade: entry 100, hard_stop 95, 90 shares, alert 3 trading days ago.
    row = _trade_row()
    conn = _FakeConn([row])
    monkeypatch.setattr(live_tracker, "get_pool",
                        lambda: asyncio.sleep(0, result=_FakePool(conn)))
    monkeypatch.setattr(live_tracker, "et_today", lambda: date(2026, 6, 23))
    # Wick bar: low 94 (<= hard_stop 95) but close 110 (> entry 100), green.
    monkeypatch.setattr(live_tracker, "get_index_history",
                        lambda *_a, **_k: asyncio.sleep(0, result=[{"l": 94.0, "c": 110.0, "h": 111.0, "o": 109.0}]))
    monkeypatch.setattr(live_tracker, "execute_partial_exit",
                        lambda *a, **k: exec_spy(*a, **k))
    # NOTE: apply_daily_exit_step is NOT mocked here — the real one runs.

    results = asyncio.run(live_tracker.run_partial_exits())

    # hold_days = (2026-06-23 - 2026-06-18) = 5 calendar days >= 3, green ->
    # partial of int(90)//3 = 30 shares must fire despite the intraday wick.
    assert calls == [(1, 30)], f"wick-day partial dropped: calls={calls}, results={results}"
    assert results[0]["action"] == "partial_submitted"


def test_no_double_fire_across_both_jobs(monkeypatch):
    # Run BOTH jobs against the same trade on the same day; the partial must be
    # submitted exactly once (by the 3:45 job).
    calls = []

    async def exec_spy(trade_id, shares, **k):
        calls.append((trade_id, shares))
        return True

    _install_common(monkeypatch, _partial_step(), exec_spy)
    asyncio.run(live_tracker.run_partial_exits())
    _install_common(monkeypatch, _partial_step(), exec_spy)  # fresh fakes, same day
    asyncio.run(live_tracker.update_open_positions_live())

    assert calls == [(1, 30)], f"partial must fire exactly once: {calls}"
